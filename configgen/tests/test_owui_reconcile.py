"""Exercise deployment against a fake API, including silent write failures."""

import copy
import importlib.util
from pathlib import Path
import pytest


def module():
    path = Path(__file__).resolve().parents[2] / "openwebui-init/reconcile_models.py"
    spec = importlib.util.spec_from_file_location("reconcile_models", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def desired():
    models = [
        {
            "id": n,
            "name": n,
            "params": {
                "temperature": 0.5,
                "enable_thinking": True,
                "thinking_budget": 81920,
                "reasoning_effort": "medium",
            },
            "meta": {},
            "is_active": True,
        }
        for n in ["Main-A", "Task-A"]
    ]
    settings = {
        "schema": 1,
        "main_model_ids": ["Main-A"],
        "task_model_id": "Task-A",
        "excluded_model_ids": ["Bench-A"],
        "defaults": {
            "DEFAULT_MODELS": "Main-A",
            "DEFAULT_PINNED_MODELS": "Main-A",
            "MODEL_ORDER_LIST": ["Main-A", "Task-A"],
        },
    }
    return models, settings


class API:
    def __init__(self):
        self.models, _ = desired()
        self.models[0]["params"]["temperature"] = 0.9
        self.models[0]["access_grants"] = [{"principal_id": "keep-me"}]
        self.connection = {
            "OPENAI_API_BASE_URLS": ["http://main/v1", "http://else/v1"],
            "OPENAI_API_KEYS": ["keep", "foreign"],
            "ENABLE_OPENAI_API": True,
            "OPENAI_API_CONFIGS": {
                "0": {"model_ids": [], "connection_type": "external"},
                "1": {"model_ids": ["Personal"], "enable": True},
            },
        }
        self.defaults = {
            "DEFAULT_MODELS": "Old",
            "DEFAULT_MODEL_PARAMS": {"temperature": 1.7},
            "DEFAULT_MODEL_METADATA": {"keep": "yes"},
        }
        self.tasks = {
            "TASK_MODEL": "Old",
            "TASK_MODEL_EXTERNAL": "Old",
            "OTHER": "keep",
        }
        self.writes = []
        self.ignore_updates = False
        self.leak = False

    def get(self, route):
        if route == "/api/v1/models/export":
            return []
        if route == "/api/v1/models/base":
            return copy.deepcopy(self.models)
        if route == "/openai/config":
            return copy.deepcopy(self.connection)
        if route == "/api/v1/configs/models":
            return copy.deepcopy(self.defaults)
        if route == "/api/v1/tasks/config":
            return copy.deepcopy(self.tasks)
        if route == "/api/models?refresh=true":
            ids = ["Main-A", "Task-A", "Personal"] + (["Bench-A"] if self.leak else [])
            return {"data": [{"id": n, "connection_type": "local"} for n in ids]}
        raise AssertionError(route)

    def post(self, route, payload):
        self.writes.append((route, copy.deepcopy(payload)))
        if self.ignore_updates:
            return payload
        if route == "/api/v1/models/model/update":
            self.models = [
                copy.deepcopy(payload) if m["id"] == payload["id"] else m
                for m in self.models
            ]
        elif route == "/api/v1/models/create":
            self.models.append(copy.deepcopy(payload))
        elif route == "/openai/config/update":
            self.connection = copy.deepcopy(payload)
        elif route == "/api/v1/configs/models":
            self.defaults = copy.deepcopy(payload)
        elif route == "/api/v1/tasks/config/update":
            self.tasks = copy.deepcopy(payload)
        else:
            raise AssertionError(route)
        return copy.deepcopy(payload)


def test_reconcile_filters_router_and_verifies_idempotently():
    m = module()
    api = API()
    models, settings = desired()
    m.reconcile(api, models, settings, "http://main/v1", "http://task/v1", apply=True)
    assert api.connection["OPENAI_API_CONFIGS"]["0"]["model_ids"] == ["Main-A"]
    assert api.connection["OPENAI_API_CONFIGS"]["1"]["model_ids"] == ["Personal"]
    assert api.connection["OPENAI_API_KEYS"][:2] == ["keep", "foreign"]
    assert api.models[0]["params"] == models[0]["params"]
    assert api.models[0]["access_grants"] == [{"principal_id": "keep-me"}]
    assert api.defaults["DEFAULT_MODELS"] == "Main-A"
    assert api.defaults["DEFAULT_MODEL_PARAMS"] == {}
    assert api.defaults["DEFAULT_MODEL_METADATA"] == {"keep": "yes"}
    assert api.tasks["TASK_MODEL_EXTERNAL"] == "Task-A" and api.tasks["OTHER"] == "keep"
    api.writes.clear()
    m.reconcile(api, models, settings, "http://main/v1", "http://task/v1", apply=True)
    assert api.writes == []


def test_dry_run_has_no_writes_and_stale_registration_fails_closed():
    m = module()
    api = API()
    models, settings = desired()
    m.reconcile(api, models, settings, "http://main/v1", "http://task/v1", apply=False)
    assert not api.writes
    api.models.append({"id": "Bench-A"})
    with pytest.raises(ValueError, match="stale"):
        m.reconcile(
            api, models, settings, "http://main/v1", "http://task/v1", apply=True
        )
    assert not api.writes


def test_success_http_with_ignored_writes_fails_readback():
    m = module()
    api = API()
    api.ignore_updates = True
    models, settings = desired()
    with pytest.raises(RuntimeError, match="verification"):
        m.reconcile(
            api, models, settings, "http://main/v1", "http://task/v1", apply=True
        )


def test_combined_list_must_not_leak_excluded_models():
    m = module()
    api = API()
    api.leak = True
    models, settings = desired()
    with pytest.raises(RuntimeError, match="visible"):
        m.reconcile(
            api, models, settings, "http://main/v1", "http://task/v1", apply=True
        )


def test_malformed_generated_policy_is_rejected_before_network():
    m = module()
    api = API()
    models, settings = desired()
    settings["main_model_ids"] = []
    with pytest.raises(ValueError):
        m.reconcile(
            api, models, settings, "http://main/v1", "http://task/v1", apply=True
        )
    assert not api.writes


def test_generated_pair_mismatch_is_rejected(tmp_path):
    import json

    m = module()
    models, settings = desired()
    settings["models_sha256"] = "wrong"
    (tmp_path / "models_config.json").write_text(json.dumps(models))
    (tmp_path / "model_settings.json").write_text(json.dumps(settings))
    with pytest.raises(ValueError, match="generated"):
        m.load_desired(tmp_path)


def test_duplicate_connections_and_legacy_url_entry_are_filtered():
    m = module()
    api = API()
    models, settings = desired()
    api.connection["OPENAI_API_BASE_URLS"].append("http://main/v1/")
    api.connection["OPENAI_API_CONFIGS"]["http://main/v1/"] = {"model_ids": []}
    m.reconcile(api, models, settings, "http://main/v1", "http://task/v1", apply=True)
    assert api.connection["OPENAI_API_CONFIGS"]["2"]["model_ids"] == ["Main-A"]
    assert "http://main/v1/" not in api.connection["OPENAI_API_CONFIGS"]


def test_removed_managed_model_is_detected_but_personal_alias_is_preserved():
    m = module()
    api = API()
    models, settings = desired()
    api.models.append(
        {"id": "Removed-from-registry", "meta": {"mlx_local_stack_managed": True}}
    )
    with pytest.raises(ValueError, match="stale"):
        m.reconcile(
            api, models, settings, "http://main/v1", "http://task/v1", apply=True
        )
    assert api.writes == []


def test_prune_backs_up_and_removes_only_stale_managed_model(tmp_path):
    import json

    m = module()
    api = API()
    models, settings = desired()
    api.models.extend(
        [{"id": "Bench-A"}, {"id": "Personal-A", "base_model_id": "Other"}]
    )
    original_post = api.post

    def post(route, payload):
        if route == "/api/v1/models/model/delete":
            api.writes.append((route, payload))
            api.models = [x for x in api.models if x["id"] != payload["id"]]
            return True
        return original_post(route, payload)

    api.post = post
    backup = tmp_path / "before.json"
    m.reconcile(
        api,
        models,
        settings,
        "http://main/v1",
        "http://task/v1",
        apply=True,
        prune=True,
        backup=backup,
    )
    assert any(x["id"] == "Bench-A" for x in json.loads(backup.read_text())["models"])
    assert any(x["id"] == "Personal-A" for x in api.models)
    assert backup.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        m.write_backup(backup, {})


def test_hidden_task_flag_must_reach_combined_model_list():
    m = module()
    api = API()
    models, settings = desired()
    settings["hidden_model_ids"] = ["Task-A"]
    models[1]["meta"]["hidden"] = True
    with pytest.raises(RuntimeError, match="selector"):
        m.reconcile(
            api, models, settings, "http://main/v1", "http://task/v1", apply=True
        )
