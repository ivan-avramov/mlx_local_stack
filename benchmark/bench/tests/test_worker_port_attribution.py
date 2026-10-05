"""M57: the worker is identified by the process that LISTENS on the registry's mlx_port, not by an
all-process argv scan (an AccessDenied argv must never read as "no worker")."""
import subprocess
import sys
import types

import pytest
import yaml

import bench.provenance as P

HF = "caslca/modelX-4bit"
ARGV_AUTO = ["python", "-m", "mlx_vlm.server", "--model", HF, "--port", "8091"]


def _registry(tmp_path, policy="fused_v1", mlx_port=8091):
    doc = {"manager_port": 8000, "models": [{"name": "m", "hf_path": HF, "attention_policy": policy}]}
    if mlx_port is not None:
        doc["mlx_port"] = mlx_port
    p = tmp_path / "reg.yaml"
    p.write_text(yaml.safe_dump(doc))
    return str(p)


def _ports(monkeypatch, table):
    """table: {port: [pids] | Exception}."""
    def fake(port):
        v = table.get(port, [])
        if isinstance(v, Exception):
            raise v
        return list(v)
    monkeypatch.setattr(P, "_port_listener_pids", fake)


def _facts(monkeypatch, by_pid):
    monkeypatch.setattr(P, "_process_facts", lambda pid: dict(
        {"pid": pid, "argv": None, "cmdline": None}, **by_pid[pid]))


def test_unreadable_worker_argv_refuses(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: [1]})
    _facts(monkeypatch, {111: {"argv": None}})
    with pytest.raises(P.ServingStateError, match="argv"):
        P.registry_attention_policy("m", _registry(tmp_path))
    with pytest.raises(P.ServingStateError):
        P.registry_lazy_prompt_embeddings("m", _registry(tmp_path))


def test_listener_on_mlx_port_is_the_worker_and_disagreement_refuses(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: [1]})
    _facts(monkeypatch, {111: {"argv": ARGV_AUTO}})         # serves auto, registry fused_v1
    with pytest.raises(P.ServingStateError, match="attention_policy"):
        P.registry_attention_policy("m", _registry(tmp_path))


def test_listener_argv_is_read_for_the_flags(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: [1]})
    _facts(monkeypatch, {111: {"argv": ARGV_AUTO + ["--attention-policy", "fused_v1"]}})
    st = P.registry_attention_policy("m", _registry(tmp_path))
    assert st == {"attention_policy": "fused_v1", "attention_policy_source": "worker"}


def test_worker_for_another_model_falls_back_to_the_registry(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111], 8000: [1]})
    _facts(monkeypatch, {111: {"argv": ["python", "-m", "mlx_vlm.server", "--model", "other/model"]}})
    st = P.registry_attention_policy("m", _registry(tmp_path))
    assert st == {"attention_policy": "fused_v1", "attention_policy_source": "registry"}


def test_two_listeners_refuse(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [111, 222], 8000: [1]})
    with pytest.raises(P.ServingStateError, match="more than one"):
        P.registry_attention_policy("m", _registry(tmp_path))


def test_no_listener_falls_back_to_the_registry(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: [], 8000: [1]})
    st = P.registry_attention_policy("m", _registry(tmp_path))
    assert st == {"attention_policy": "fused_v1", "attention_policy_source": "registry"}


def test_lookup_failure_with_a_router_up_refuses(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: PermissionError("lsof denied"), 8000: [1]})
    with pytest.raises(P.ServingStateError, match="observ"):
        P.registry_attention_policy("m", _registry(tmp_path))


def test_lookup_failure_with_no_router_falls_back(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: PermissionError("lsof denied"), 8000: []})
    st = P.registry_attention_policy("m", _registry(tmp_path))
    assert st["attention_policy_source"] == "registry"


def test_lookup_failure_on_both_ports_refuses(monkeypatch, tmp_path):
    _ports(monkeypatch, {8091: PermissionError("x"), 8000: PermissionError("x")})
    with pytest.raises(P.ServingStateError):
        P.registry_attention_policy("m", _registry(tmp_path))


def test_registry_without_mlx_port_identifies_no_worker(monkeypatch, tmp_path):
    _ports(monkeypatch, {8000: [1]})
    st = P.registry_attention_policy("m", _registry(tmp_path, mlx_port=None))
    assert st["attention_policy_source"] == "registry"


def test_no_stack_and_no_mlx_port_falls_back(monkeypatch, tmp_path):
    _ports(monkeypatch, {})
    st = P.registry_attention_policy("m", _registry(tmp_path, mlx_port=None))
    assert st["attention_policy_source"] == "registry"


def test_unrelated_unreadable_and_zombie_processes_do_not_refuse(monkeypatch):
    class Denied(Exception):
        pass

    class Proc:
        def __init__(self, pid, conns):
            self.pid, self._c = pid, conns

        def net_connections(self, kind="inet"):
            if isinstance(self._c, Exception):
                raise self._c
            return self._c

    ok = [types.SimpleNamespace(status="LISTEN", laddr=types.SimpleNamespace(ip="127.0.0.1", port=8091))]
    fake = types.SimpleNamespace(
        CONN_LISTEN="LISTEN",
        process_iter=lambda attrs=None: [Proc(5, Denied("AccessDenied")), Proc(6, Denied("zombie")),
                                         Proc(7, ok)])
    monkeypatch.setitem(sys.modules, "psutil", fake)
    monkeypatch.setattr(P.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 1, stdout="", stderr=""))                          # lsof: rc 1 = no match
    assert P._port_listener_pids(8091) == [7]


def test_lsof_failure_is_an_observation_failure(monkeypatch):
    monkeypatch.setitem(sys.modules, "psutil", types.SimpleNamespace(
        CONN_LISTEN="LISTEN", process_iter=lambda attrs=None: []))

    def boom(*a, **k):
        raise FileNotFoundError("lsof")
    monkeypatch.setattr(P.subprocess, "run", boom)
    with pytest.raises(Exception):
        P._port_listener_pids(8091)
