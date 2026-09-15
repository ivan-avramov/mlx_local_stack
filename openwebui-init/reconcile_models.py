"""Apply configgen's OpenWebUI models and deployment policy, then verify readback."""

from __future__ import annotations

from copy import deepcopy
import json
import hashlib
import os
from pathlib import Path

import requests


class API:
    def __init__(self, url: str, headers: dict):
        self.url = url.rstrip("/")
        self.headers = headers

    def request(self, method, route, payload=None):
        response = requests.request(
            method, self.url + route, headers=self.headers, json=payload, timeout=30
        )
        if not response.ok:
            raise RuntimeError(f"{method} {route}: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"{method} {route}: expected JSON; API route may have changed"
            ) from exc

    def get(self, route):
        return self.request("GET", route)

    def post(self, route, payload):
        return self.request("POST", route, payload)


def authenticate(url, email, password):
    if not email or not password:
        raise ValueError("OWUI_ADMIN_EMAIL and OWUI_ADMIN_PASSWORD are required")
    data = API(url, {}).post(
        "/api/v1/auths/signin", {"email": email, "password": password}
    )
    return {"Authorization": "Bearer " + data["token"]}


def load_desired(directory=None):
    directory = Path(directory or Path(__file__).resolve().parent)
    raw = (directory / "models_config.json").read_bytes()
    models = json.loads(raw)
    settings = json.loads((directory / "model_settings.json").read_text())
    if settings.get("models_sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("Mismatched generated OpenWebUI files; run configgen generate")
    validate(models, settings)
    return models, settings


def validate(models, settings):
    ids = [m["id"] for m in models]
    main = settings["main_model_ids"]
    task = settings["task_model_id"]
    excluded = settings["excluded_model_ids"]
    expected = main + ([task] if task else [])
    if (
        settings.get("schema") != 1
        or not main
        or not task
        or len(set(ids)) != len(ids)
        or len(set(expected)) != len(expected)
        or set(ids) != set(expected)
        or set(ids) & set(excluded)
    ):
        raise ValueError(
            "Invalid or mismatched generated OpenWebUI policy; run configgen generate"
        )
    defaults = settings["defaults"]
    if (
        defaults["DEFAULT_MODELS"] not in main
        or defaults["DEFAULT_PINNED_MODELS"] not in main
        or len(defaults["MODEL_ORDER_LIST"]) != len(ids)
        or set(defaults["MODEL_ORDER_LIST"]) != set(ids)
    ):
        raise ValueError("Invalid OpenWebUI default/order policy")
    for m in models:
        if not isinstance(m["params"], dict) or not isinstance(m["meta"], dict):
            raise ValueError("Invalid model params/meta")


def normalize(value):
    # OWUI adds optional null metadata fields on readback.
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def projection(model):
    return normalize(
        {
            k: model.get(k, True if k == "is_active" else None)
            for k in ("name", "params", "meta", "is_active", "base_model_id")
        }
    )


def connection_config(current, settings, main_url, task_url):
    result = deepcopy(current)
    urls = result.setdefault("OPENAI_API_BASE_URLS", [])
    keys = result.setdefault("OPENAI_API_KEYS", [])
    configs = result.setdefault("OPENAI_API_CONFIGS", {})
    for url, ids in (
        (main_url, settings["main_model_ids"]),
        (task_url, [settings["task_model_id"]]),
    ):
        matches = [
            i for i, value in enumerate(urls) if value.rstrip("/") == url.rstrip("/")
        ]
        if not matches:
            urls.append(url)
            matches = [len(urls) - 1]
        while len(keys) < len(urls):
            keys.append("not-needed")
        # Update duplicate or legacy URL-keyed entries too, preventing discovery leaks.
        for index in matches:
            entry = configs.setdefault(
                str(index), deepcopy(configs.get(urls[index], {}))
            )
            entry.update(
                model_ids=list(ids), enable=True, connection_type="local", prefix_id=""
            )
            configs.pop(urls[index], None)
    result["ENABLE_OPENAI_API"] = True
    return result


def read_state(api):
    # Current OWUI separates native provider defaults (base) from custom aliases (export).
    models = []
    for route in ("/api/v1/models/base", "/api/v1/models/export"):
        entries = api.get(route)
        if not isinstance(entries, list):
            raise RuntimeError(
                "Unexpected saved-model response; reconciliation aborted"
            )
        models.extend(entries)
    if len({m["id"] for m in models}) != len(models):
        raise RuntimeError("Duplicate saved-model IDs; reconciliation aborted")
    return {
        "models": models,
        "connections": api.get("/openai/config"),
        "defaults": api.get("/api/v1/configs/models"),
        "tasks": api.get("/api/v1/tasks/config"),
    }


def write_backup(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The connection snapshot may contain provider keys; refuse overwrite, restrict access.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def reconcile(
    api, models, settings, main_url, task_url, *, apply=False, prune=False, backup=None
):
    validate(models, settings)
    state = read_state(api)
    remote = {m["id"]: m for m in state["models"]}
    desired_ids = {m["id"] for m in models}
    retired = {
        m["id"]
        for m in state["models"]
        if (m.get("meta") or {}).get("mlx_local_stack_managed") is True
        and m["id"] not in desired_ids
    }
    excluded = set(settings["excluded_model_ids"]) | retired
    stale = sorted(set(remote) & excluded)
    if stale and apply and not prune:
        raise ValueError(
            "stale saved registrations: "
            + ", ".join(stale)
            + "; review and use publish_models.py --prune with a backup"
        )
    if stale and apply and not backup:
        raise ValueError("A backup is required before pruning stale registrations")
    if backup and apply:
        write_backup(backup, state)

    updates = [
        m
        for m in models
        if m["id"] not in remote or projection(m) != projection(remote[m["id"]])
    ]
    connections = connection_config(state["connections"], settings, main_url, task_url)
    defaults = {**state["defaults"], **settings["defaults"], "DEFAULT_MODEL_PARAMS": {}}
    tasks = {
        **state["tasks"],
        "TASK_MODEL": settings["task_model_id"],
        "TASK_MODEL_EXTERNAL": settings["task_model_id"],
    }
    changed = {
        "models": [m["id"] for m in updates],
        "stale": stale,
        "connections": connections != state["connections"],
        "defaults": defaults != state["defaults"],
        "tasks": tasks != state["tasks"],
    }
    print(json.dumps(changed, indent=2))
    if not apply:
        return changed
    for model in updates:
        previous = remote.get(model["id"], {})
        payload = {k: model[k] for k in ("id", "name", "params", "meta")}
        payload.update(
            is_active=True,
            base_model_id=None,
            access_grants=previous.get("access_grants")
            or model.get("access_grants", []),
        )
        route = (
            "/api/v1/models/create" if not previous else "/api/v1/models/model/update"
        )
        api.post(route, payload)
    for model_id in stale:
        api.post("/api/v1/models/model/delete", {"id": model_id})
    if changed["connections"]:
        api.post("/openai/config/update", connections)
    if changed["defaults"]:
        api.post("/api/v1/configs/models", defaults)
    if changed["tasks"]:
        api.post("/api/v1/tasks/config/update", tasks)

    after = read_state(api)
    by_id = {m["id"]: m for m in after["models"]}
    if (
        any(
            m["id"] not in by_id or projection(m) != projection(by_id[m["id"]])
            for m in models
        )
        or set(by_id) & excluded
        or normalize(after["connections"]) != normalize(connections)
        or any(after["defaults"].get(k) != v for k, v in settings["defaults"].items())
        or after["defaults"].get("DEFAULT_MODEL_PARAMS") not in ({}, None)
        or any(
            after["tasks"].get(k) != settings["task_model_id"]
            for k in ("TASK_MODEL", "TASK_MODEL_EXTERNAL")
        )
    ):
        raise RuntimeError("OpenWebUI configuration verification failed")
    visible = api.get("/api/models?refresh=true")
    entries = visible.get("data", []) if isinstance(visible, dict) else visible
    ids = {m["id"] for m in entries}
    expected = {m["id"] for m in models}
    if not expected <= ids or ids & excluded:
        raise RuntimeError("OpenWebUI visible model list verification failed")
    for m in entries:
        if m["id"] in expected and m.get("connection_type") != "local":
            raise RuntimeError("OpenWebUI task-routing connection verification failed")
    print(
        f"Verified {len(expected)} shipped model registrations, defaults and discovery policy."
    )
    return changed
