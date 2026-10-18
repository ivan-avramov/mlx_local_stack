"""P371 review r1 F2: production M64 binds worker receipts `required` with an HTTP source pointed at the worker control
endpoint; while the endpoint does not exist (P372) the source refuses before any spawn; tg1 stays `absent`."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import run_oc_probe
from bench import arm_opencode, arm_runner, arm_specs, provenance, tg1_runner
from bench import worker_receipts as wr
from bench.tests.p371_world import evidence, rows, run_core, world      # noqa: F401  (fixture)


def test_production_m64_binds_worker_receipts_required():
    assert arm_opencode.m64_evidence().worker_receipts == "required"
    assert arm_specs.OC.evidence_policy["worker_receipts"] == "required"
    assert arm_specs.OC.evidence_policy == arm_opencode.m64_evidence().as_dict()


def test_tg1_stays_receipts_absent():
    assert tg1_runner.TG1_EVIDENCE.worker_receipts == "absent"


def test_the_oc_entry_binds_an_http_source_at_the_registry_worker_port(monkeypatch, tmp_path):
    reg = tmp_path / "registry.yaml"
    reg.write_text("mlx_port: 8123\n")
    monkeypatch.setattr(provenance.paths, "registry_path", lambda: reg)
    monkeypatch.setenv("MLX_VLM_SERVER_API_KEY", "k")
    evidence_, source = run_oc_probe.production_binding()
    assert evidence_.worker_receipts == "required"
    assert isinstance(source, wr.HttpReceiptSource) and source.base == "http://127.0.0.1:8123" and source.api_key == "k"


class Handler(BaseHTTPRequestHandler):
    status = 404

    def do_GET(self):
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def endpoint():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def test_an_unreachable_endpoint_refuses_naming_p372():
    with pytest.raises(wr.ReceiptUnavailable, match="P372"):
        wr.HttpReceiptSource("http://127.0.0.1:9", timeout_s=1).check()


def test_a_worker_without_the_endpoint_refuses_naming_p372(endpoint):
    Handler.status = 404
    with pytest.raises(wr.ReceiptUnavailable, match="P372"):
        wr.HttpReceiptSource(endpoint, timeout_s=2).check()


def test_a_worker_that_serves_the_route_passes_the_check(endpoint):
    Handler.status = 405                      # a POST-only route answers GET with 405: it exists
    wr.HttpReceiptSource(endpoint, timeout_s=2).check()


def test_required_with_an_unreachable_endpoint_refuses_before_any_spawn(world):
    with pytest.raises(SystemExit, match="REFUSED.*P372"):
        run_core(world, evidence_=evidence(worker_receipts="required"),
                 receipts=wr.HttpReceiptSource("http://127.0.0.1:9", timeout_s=1))
    assert not (world.tmp / "rows.jsonl").exists()
    assert not list((world.tmp / "neutral_evidence").rglob("*.events.jsonl")) if (world.tmp / "neutral_evidence").exists() else True
