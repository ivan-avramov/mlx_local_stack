"""apply_rag_embedding_config: engine routing, co-hosted endpoint, readback."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# init.py reads its container environment at import time; dummies for a CPU test.
for _k, _v in {"OWUI_URL": "http://owui.invalid", "OWUI_ADMIN_EMAIL": "x@example.invalid",
               "OWUI_ADMIN_PASSWORD": "x"}.items():
    os.environ.setdefault(_k, _v)

import init  # noqa: E402

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class R:
    def __init__(self, code, payload):
        self.status_code = code
        self._p = payload

    def json(self):
        return self._p


def _stub(monkeypatch, calls, existing=None, mutate=None):
    """Wire requests.get/post to an in-memory config store."""
    current = existing if existing is not None else {
        "RAG_EMBEDDING_ENGINE": "",
        "RAG_EMBEDDING_MODEL": MODEL,
        "RAG_EMBEDDING_BATCH_SIZE": 1,
        "openai_config": {"url": "https://api.openai.com/v1", "key": ""},
    }

    def get(url, headers=None):
        calls["get_url"] = url
        return R(200, dict(current))

    def post(url, headers=None, json=None):
        calls["post_url"] = url
        calls["sent"] = json
        echoed = dict(json)
        if mutate:
            echoed.update(mutate)
        return R(200, echoed)

    monkeypatch.setattr(init.requests, "get", get)
    monkeypatch.setattr(init.requests, "post", post)


def test_engine_is_openai_so_nothing_is_downloaded_in_the_container(monkeypatch):
    """An empty engine means in-container SentenceTransformers, which fetches
    from Hugging Face at boot -- fatal offline and behind TLS inspection."""
    calls = {}
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    _stub(monkeypatch, calls)
    init.apply_rag_embedding_config({})
    assert calls["sent"]["RAG_EMBEDDING_ENGINE"] == "openai"
    assert calls["sent"]["RAG_EMBEDDING_MODEL"] == MODEL


def test_it_points_at_the_co_hosted_task_model_instance(monkeypatch):
    """Not the :8000 router: mlx-serve's /v1/embeddings unloads the resident
    chat model on every call. The task-model mlx_vlm instance keeps embedding
    models in a separate cache group, so they live alongside it."""
    calls = {}
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    monkeypatch.setenv("TASK_MODEL_PORT", "8092")
    _stub(monkeypatch, calls)
    init.apply_rag_embedding_config({})
    assert calls["sent"]["openai_config"]["url"] == "http://host.docker.internal:8092/v1"


def test_the_port_follows_the_environment(monkeypatch):
    calls = {}
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    monkeypatch.setenv("TASK_MODEL_PORT", "9999")
    _stub(monkeypatch, calls)
    init.apply_rag_embedding_config({})
    assert calls["sent"]["openai_config"]["url"] == "http://host.docker.internal:9999/v1"


def test_it_targets_the_retrieval_embedding_endpoints(monkeypatch):
    calls = {}
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    _stub(monkeypatch, calls)
    init.apply_rag_embedding_config({})
    assert calls["get_url"].endswith("/api/v1/retrieval/embedding")
    assert calls["post_url"].endswith("/api/v1/retrieval/embedding/update")


def test_unset_model_skips_without_touching_the_config(monkeypatch):
    """runserver.sh always exports it; a bare `docker compose up` does not.
    Leaving OWUI's default alone beats aborting the whole bring-up."""
    calls = {}
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    _stub(monkeypatch, calls)
    init.apply_rag_embedding_config({})  # must not raise
    assert "sent" not in calls, "nothing may be pushed when no model is configured"


def test_readback_drift_warns_but_does_not_abort(monkeypatch):
    """Same precedent as the web-search and ollama pushes: the image is
    unpinned, so an upstream rename must not take the whole stack down."""
    calls = {}
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    _stub(monkeypatch, calls, mutate={"RAG_EMBEDDING_ENGINE": ""})
    init.apply_rag_embedding_config({})  # must not raise
